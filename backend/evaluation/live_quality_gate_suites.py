"""Suite runners for live alpha quality gates."""

from __future__ import annotations

import base64
import time
import wave
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any

import httpx

try:
    from backend.evaluation.live_quality_gate_utils import (
        EndpointPacer,
        GateResult,
        check_answer_quality,
        compact,
        denies_explicit_ltm_recall,
        recalled_facts,
        record,
        required_sources_for_case,
        response_route,
        source_gate_sources,
        source_requirement_ok,
        _render_template,
        post_json,
    )
except ImportError:  # pragma: no cover - supports `python -m evaluation...` from backend/
    from evaluation.live_quality_gate_utils import (
        EndpointPacer,
        GateResult,
        check_answer_quality,
        compact,
        denies_explicit_ltm_recall,
        recalled_facts,
        record,
        required_sources_for_case,
        response_route,
        source_gate_sources,
        source_requirement_ok,
        _render_template,
        post_json,
    )


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
        metadata = chat.get("metadata") if isinstance(chat.get("metadata"), dict) else {}
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
        max_latency_ms = int(case.get("max_latency_ms", 15000))
        warn_latency_ms = int(case.get("warn_latency_ms", 10000))
        sources_ok, missing_sources = source_requirement_ok(
            metadata,
            required_sources_for_case(case),
        )
        actual_sources = sorted(source_gate_sources(metadata))
        if not route_ok:
            status = "FAIL"
        elif not sources_ok:
            status = "FAIL"
        elif duration_ms > max_latency_ms:
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
        if missing_sources:
            notes_parts.append(f"missing_sources={missing_sources}")
        if duration_ms > warn_latency_ms:
            notes_parts.append(f"latency={duration_ms}ms")
        if actual_sources:
            notes_parts.append(f"sources={actual_sources}")
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
            found = recalled_facts(last_answer, facts)
            if http != 200:
                status = "FAIL"
            elif len(found) == len(facts):
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
            elif "cafe-free" in last_answer.lower():
                status = "WARN"
                notes = "明示的なLTM昇格なしに具体SSIDが保持されている可能性あり"
            elif "ssid" in last_answer.lower() and not denies_explicit_ltm_recall(last_answer):
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
