#!/usr/bin/env bash
set -euo pipefail

# Live voice pipeline preflight for alpha GO/no-GO.
#
# Validates the critical path without slide narration:
#   STT warmup -> PiperPlus source TTS -> Qwen-primary STT -> LangGraph route -> PiperPlus answer TTS
#
# Usage:
#   scripts/voice-pipeline-live-preflight.sh
#   scripts/voice-pipeline-live-preflight.sh --host https://... --key "$API_SECRET_KEY"
#   scripts/voice-pipeline-live-preflight.sh --case-set extended --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VOICE_PIPELINE_ROOT_DIR="$ROOT_DIR"

python3 - "$@" <<'PY'
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any


DEFAULT_URL = "https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
ROOT_DIR = pathlib.Path(os.environ["VOICE_PIPELINE_ROOT_DIR"])


@dataclass(frozen=True)
class Case:
    case_id: str
    language: str
    expected_route: str
    query: str


SMOKE_CASES = [
    Case("VP-BIZ-001", "ja", "business_info", "エンジニアカフェの営業時間を教えてください。"),
    Case("VP-FAC-001", "ja", "facility", "Wi-Fi の接続方法を教えてください。"),
    Case("VP-EVT-001", "ja", "event", "今日開催されるイベントを教えてください。"),
    Case("VP-GEN-001", "ja", "general_knowledge", "Python の仮想環境とは何ですか。"),
]

EXTENDED_CASES = [
    *SMOKE_CASES,
    Case("VP-BIZ-EN-001", "en", "business_info", "Can I use Engineer Cafe without a reservation?"),
    Case("VP-FAC-EN-001", "en", "facility", "How can I connect to the Wi-Fi?"),
    Case("VP-EVT-EN-001", "en", "event", "What events are happening at Engineer Cafe this week?"),
    Case("VP-GEN-EN-001", "en", "general_knowledge", "What is the difference between an API and an SDK?"),
]


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


def tts_fallback_problem(body: dict[str, Any]) -> str:
    upstream = body.get("upstreamStatus") if isinstance(body.get("upstreamStatus"), dict) else {}
    if upstream.get("fallbackUsed") is True:
        return compact(upstream.get("error") or body.get("error") or "fallbackUsed=true")
    clean_text = str(body.get("cleanText") or "")
    fallback_phrases = (
        "音声の生成に失敗しました",
        "failed to generate the audio response",
        "Failed to generate speech",
    )
    if any(phrase in clean_text for phrase in fallback_phrases):
        return compact(clean_text)
    return ""


def similarity(expected: str, actual: str) -> float:
    def norm(text: str) -> str:
        return "".join(text.lower().split())

    return SequenceMatcher(None, norm(expected), norm(actual)).ratio()


def fetch_api_key(args: argparse.Namespace) -> str:
    if args.key:
        return args.key
    env_key = os.getenv("API_SECRET_KEY") or os.getenv("BACKEND_API_KEY")
    if env_key:
        return env_key
    if args.dry_run:
        return ""
    try:
        result = subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={args.secret_name}",
                f"--project={args.secret_project}",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def post_json(
    *,
    base_url: str,
    api_key: str,
    endpoint: str,
    body: dict[str, Any],
    timeout: int,
) -> tuple[int, int, dict[str, Any], str]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    started = time.perf_counter()
    raw = ""
    status = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
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
    rows: list[dict[str, Any]],
    *,
    case_id: str,
    step: str,
    status: str,
    http: int,
    duration_ms: int,
    language: str,
    expected: str,
    actual: str,
    notes: str = "",
) -> None:
    rows.append(
        {
            "timestamp": utc_now(),
            "case_id": case_id,
            "step": step,
            "status": status,
            "http": http,
            "duration_ms": duration_ms,
            "language": language,
            "expected": expected,
            "actual": actual,
            "notes": notes,
        }
    )
    print(
        f"[{status}] {case_id} {step} http={http} duration_ms={duration_ms} "
        f"expected={compact(expected, 48)} actual={compact(actual, 72)}"
    )


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "PASS": sum(1 for row in rows if row["status"] == "PASS"),
        "WARN": sum(1 for row in rows if row["status"] == "WARN"),
        "FAIL": sum(1 for row in rows if row["status"] == "FAIL"),
    }


def percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * ratio)
    return ordered[index]


def write_reports(
    *,
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    report_md: pathlib.Path,
    report_csv: pathlib.Path,
) -> None:
    report_md.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "case_id",
        "step",
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
        writer.writerows(rows)

    counts = status_counts(rows)
    by_step: dict[str, list[int]] = {}
    for row in rows:
        try:
            by_step.setdefault(str(row["step"]), []).append(int(row["duration_ms"]))
        except Exception:
            pass

    lines = [
        "# Voice Pipeline Live Preflight",
        "",
        f"- Timestamp: {args.timestamp}",
        f"- Backend: {args.host}",
        f"- Case set: {args.case_set}",
        f"- TTS provider: {args.tts_provider}",
        f"- Strict Qwen primary: {'no' if args.allow_vosk_fallback else 'yes'}",
        f"- STT warn/max: {args.stt_warn_ms}ms / {args.stt_max_ms}ms",
        f"- Similarity threshold: {args.stt_similarity_threshold}",
        f"- Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL",
        f"- Detail CSV: {report_csv.name}",
        "",
        "## Gate Position",
        "",
        "- Welcome warmup の実装を、STT初回速度の補助導線として扱う。",
        "- GO判断は同一セッションの STT provider、LangGraph route、PiperPlus 出力で判定する。",
        "- スライド差し替え予定のため、slide narration はこの gate から除外する。",
        "",
        "## Latency",
        "",
        "| Step | Count | p50 ms | p95 ms | max ms |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for step in sorted(by_step):
        values = by_step[step]
        lines.append(
            f"| {step} | {len(values)} | {percentile(values, 0.50)} | "
            f"{percentile(values, 0.95)} | {max(values)} |"
        )

    problem_rows = [row for row in rows if row["status"] in {"FAIL", "WARN"}]
    if problem_rows:
        lines.extend(["", "## Problems", "", "| Status | Case | Step | Expected | Actual | Notes |", "| --- | --- | --- | --- | --- | --- |"])
        for row in problem_rows[:80]:
            lines.append(
                f"| {row['status']} | {row['case_id']} | {row['step']} | "
                f"{compact(row['expected'])} | {compact(row['actual'])} | {compact(row['notes'])} |"
            )

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def warmup_gate(args: argparse.Namespace, api_key: str, rows: list[dict[str, Any]]) -> None:
    session_id = f"voice-pipeline-warmup-{args.timestamp}"
    body = {"action": "warmup", "language": "ja", "sessionId": session_id}
    http, duration_ms, parsed, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/voice",
        body=body,
        timeout=args.timeout,
    )
    warmup_status = str(parsed.get("sttWarmupStatus") or "")
    provider = str(parsed.get("sttWarmupProvider") or "")
    if http == 200 and warmup_status in {"started", "warming", "ready"}:
        status = "PASS"
    elif http == 200 and warmup_status == "skipped" and not args.allow_warmup_skipped:
        status = "FAIL"
    elif http == 200 and warmup_status == "skipped":
        status = "WARN"
    else:
        status = "FAIL"
    record(
        rows,
        case_id="VP-WARMUP",
        step="warmup_start",
        status=status,
        http=http,
        duration_ms=duration_ms,
        language="ja",
        expected="started|warming|ready",
        actual=f"{warmup_status}:{provider}",
        notes=compact(raw),
    )

    deadline = time.monotonic() + args.warmup_poll_seconds
    last_status = warmup_status
    last_provider = provider
    while warmup_status in {"started", "warming"} and time.monotonic() < deadline:
        time.sleep(args.warmup_poll_interval)
        http, duration_ms, parsed, raw = post_json(
            base_url=args.host,
            api_key=api_key,
            endpoint="/api/voice",
            body=body,
            timeout=args.timeout,
        )
        warmup_status = str(parsed.get("sttWarmupStatus") or "")
        provider = str(parsed.get("sttWarmupProvider") or "")
        last_status = warmup_status or last_status
        last_provider = provider or last_provider
        if warmup_status in {"ready", "failed", "skipped"}:
            break

    if last_status == "ready":
        status = "PASS"
    elif args.require_warmup_ready:
        status = "FAIL"
    else:
        status = "WARN"
    record(
        rows,
        case_id="VP-WARMUP",
        step="warmup_ready",
        status=status,
        http=http,
        duration_ms=duration_ms,
        language="ja",
        expected="ready",
        actual=f"{last_status}:{last_provider}",
        notes=f"poll_seconds={args.warmup_poll_seconds}",
    )


def run_case(args: argparse.Namespace, api_key: str, rows: list[dict[str, Any]], case: Case) -> None:
    session_id = f"voice-pipeline-{args.timestamp}-{case.case_id}"

    http, duration_ms, tts_source, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/voice",
        body={
            "action": "text_to_speech",
            "text": case.query,
            "language": case.language,
            "sessionId": session_id,
            "ttsProvider": args.tts_provider,
        },
        timeout=args.timeout,
    )
    audio = tts_source.get("audioResponse")
    fallback_problem = tts_fallback_problem(tts_source)
    if (
        http == 200
        and tts_source.get("success") is True
        and isinstance(audio, str)
        and len(audio) > 64
        and not fallback_problem
    ):
        record(
            rows,
            case_id=case.case_id,
            step="piper_source_tts",
            status="PASS",
            http=http,
            duration_ms=duration_ms,
            language=case.language,
            expected=args.tts_provider,
            actual=str(tts_source.get("audioFormat") or "audio"),
            notes=f"audio_chars={len(audio)}",
        )
    else:
        record(
            rows,
            case_id=case.case_id,
            step="piper_source_tts",
            status="FAIL",
            http=http,
            duration_ms=duration_ms,
            language=case.language,
            expected="audioResponse without fallback",
            actual="fallback" if fallback_problem else "missing",
            notes=fallback_problem or compact(raw),
        )
        return

    http, duration_ms, stt, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/voice",
        body={
            "action": "speech_to_text",
            "audioData": audio,
            "language": case.language,
            "sessionId": session_id,
        },
        timeout=args.timeout,
    )
    transcript = str(stt.get("transcript") or "").strip()
    provider = str(stt.get("sttProvider") or "")
    sim = similarity(case.query, transcript) if transcript else 0.0
    expected_provider = (
        "provider=qwen-primary|vosk-fallback"
        if args.allow_vosk_fallback
        else "provider=qwen-primary"
    )
    provider_ok = provider == "qwen-primary" or (
        args.allow_vosk_fallback and provider == "vosk-fallback"
    )
    latency_ok = duration_ms <= args.stt_max_ms
    hard_latency_ok = duration_ms <= args.stt_hard_max_ms
    if not (http == 200 and stt.get("success") is True and transcript):
        stt_status = "FAIL"
    elif not provider_ok:
        stt_status = "FAIL"
    elif not hard_latency_ok:
        stt_status = "FAIL"
    elif duration_ms > args.stt_warn_ms or sim < args.stt_similarity_threshold:
        stt_status = "WARN"
    else:
        stt_status = "PASS"
    record(
        rows,
        case_id=case.case_id,
        step="qwen_primary_stt",
        status=stt_status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=f"{expected_provider} latency<={args.stt_max_ms}ms hard<={args.stt_hard_max_ms}ms",
        actual=f"provider={provider or 'unknown'} similarity={sim:.3f} transcript={compact(transcript)}",
        notes=compact(raw),
    )
    if not transcript:
        return

    http, duration_ms, chat, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/chat",
        body={
            "query": transcript,
            "language": case.language,
            "session_id": session_id,
        },
        timeout=args.timeout,
    )
    answer = str(chat.get("answer") or "").strip()
    actual_route = response_route(chat)
    if http == 200 and answer and actual_route == case.expected_route:
        route_status = "PASS"
    else:
        route_status = "FAIL"
    record(
        rows,
        case_id=case.case_id,
        step="langgraph_route",
        status=route_status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=case.expected_route,
        actual=actual_route or "unknown",
        notes=f"answer={compact(answer)} raw={compact(raw, 80)}",
    )
    if not answer:
        return

    http, duration_ms, tts_answer, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/voice",
        body={
            "action": "text_to_speech",
            "text": answer,
            "language": case.language,
            "sessionId": session_id,
            "ttsProvider": args.tts_provider,
        },
        timeout=args.timeout,
    )
    answer_audio = tts_answer.get("audioResponse")
    fallback_problem = tts_fallback_problem(tts_answer)
    if (
        http == 200
        and tts_answer.get("success") is True
        and isinstance(answer_audio, str)
        and len(answer_audio) > 64
        and not fallback_problem
    ):
        answer_status = "PASS"
        actual = str(tts_answer.get("audioFormat") or "audio")
    else:
        answer_status = "FAIL"
        actual = "fallback" if fallback_problem else "missing"
    record(
        rows,
        case_id=case.case_id,
        step="piper_answer_tts",
        status=answer_status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=f"{args.tts_provider} without fallback",
        actual=actual,
        notes=fallback_problem or compact(raw),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live STT -> LangGraph -> PiperPlus pipeline gate for alpha."
    )
    parser.add_argument("--host", default=os.getenv("VOICE_PIPELINE_BASE_URL", DEFAULT_URL))
    parser.add_argument("--key", default="")
    parser.add_argument("--secret-project", default=os.getenv("VOICE_PIPELINE_SECRET_PROJECT", "aipartner-426616"))
    parser.add_argument("--secret-name", default="API_SECRET_KEY")
    parser.add_argument("--output-dir", default=str(ROOT_DIR / "backend/tests/reports"))
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--case-set", choices=("smoke", "extended"), default="smoke")
    parser.add_argument("--tts-provider", default="piper")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--stt-warn-ms", type=int, default=5000)
    parser.add_argument("--stt-max-ms", type=int, default=10000)
    parser.add_argument("--stt-hard-max-ms", type=int, default=45000)
    parser.add_argument("--stt-similarity-threshold", type=float, default=0.50)
    parser.add_argument("--warmup-poll-seconds", type=int, default=30)
    parser.add_argument("--warmup-poll-interval", type=float, default=2.0)
    parser.add_argument("--require-warmup-ready", action="store_true")
    parser.add_argument("--allow-warmup-skipped", action="store_true")
    parser.add_argument("--allow-vosk-fallback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = EXTENDED_CASES if args.case_set == "extended" else SMOKE_CASES
    output_dir = pathlib.Path(args.output_dir)
    report_md = output_dir / f"voice-pipeline-live-{args.timestamp}.md"
    report_csv = output_dir / f"voice-pipeline-live-{args.timestamp}.csv"

    if args.dry_run:
        print("Dry run: no live API calls will be executed.")
        print(f"Backend: {args.host}")
        print(f"Case set: {args.case_set} ({len(cases)} cases)")
        print(f"TTS provider: {args.tts_provider}")
        print(f"Reports: {report_md} / {report_csv}")
        for case in cases:
            print(f"- {case.case_id}: {case.language} {case.expected_route} {case.query}")
        return 0

    api_key = fetch_api_key(args)
    if not api_key:
        print(
            "Error: API_SECRET_KEY/BACKEND_API_KEY is required "
            "(pass --key, set env, or allow gcloud Secret Manager access)",
            file=sys.stderr,
        )
        return 2

    rows: list[dict[str, Any]] = []
    warmup_gate(args, api_key, rows)
    if args.sleep > 0:
        time.sleep(args.sleep)
    for case in cases:
        run_case(args, api_key, rows, case)
        if args.sleep > 0:
            time.sleep(args.sleep)

    write_reports(rows=rows, args=args, report_md=report_md, report_csv=report_csv)
    counts = status_counts(rows)
    print(report_md)
    print(f"Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
