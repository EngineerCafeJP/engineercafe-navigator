"""
On-site voice live proof for alpha GO decisions.

This runner is intentionally separate from CI fixture tests. It uses WAV files
recorded from the actual kiosk/microphone environment and sends them to the
same live APIs used by the product:

  /api/voice speech_to_text -> /api/chat -> /api/voice text_to_speech

The manifest controls expected route, transcript, facts, and live source
metadata so the output can be attached to #571 without relying on golden-only
RAGAS context.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
DEFAULT_REPORTS_DIR = Path(__file__).parent.parent / "tests" / "reports"


@dataclass(frozen=True)
class Case:
    case_id: str
    audio_path: Path
    language: str
    expected_route: str
    expected_transcript: str
    expected_facts: list[Any]
    required_sources: list[str]


@dataclass
class Result:
    timestamp: str
    case_id: str
    step: str
    status: str
    http: int
    duration_ms: int
    language: str
    expected: str
    actual: str
    notes: str


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact(value: Any, max_len: int = 160) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text[:max_len]


def normalize(text: str) -> str:
    return "".join(text.lower().split())


def similarity(expected: str, actual: str) -> float:
    if not expected or not actual:
        return 0.0
    return SequenceMatcher(None, normalize(expected), normalize(actual)).ratio()


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


def flatten_metadata_sources(value: Any) -> set[str]:
    sources: set[str] = set()
    if isinstance(value, str):
        sources.add(value.strip().lower())
    elif isinstance(value, list):
        for item in value:
            sources.update(flatten_metadata_sources(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            sources.add(str(key).strip().lower())
            sources.update(flatten_metadata_sources(item))
    return {source for source in sources if source}


def source_requirement_ok(
    metadata: dict[str, Any], required_sources: list[str]
) -> tuple[bool, list[str]]:
    if not required_sources:
        return True, []
    actual_sources = flatten_metadata_sources(metadata.get("sources"))
    missing: list[str] = []
    for requirement in required_sources:
        alternatives = [part.strip().lower() for part in requirement.split("|") if part.strip()]
        if not any(alt in actual_sources for alt in alternatives):
            missing.append(requirement)
    return not missing, missing


def fact_in_answer(fact: Any, answer: str, threshold: float) -> bool:
    if isinstance(fact, list):
        return any(fact_in_answer(item, answer, threshold) for item in fact)
    text = str(fact)
    if "|" in text:
        return any(fact_in_answer(part.strip(), answer, threshold) for part in text.split("|"))
    if text in answer:
        return True
    norm_fact = normalize(text)
    norm_answer = normalize(answer)
    if norm_fact in norm_answer:
        return True
    return SequenceMatcher(None, norm_fact, norm_answer).ratio() >= threshold


def post_json(
    *,
    base_url: str,
    api_key: str,
    endpoint: str,
    body: dict[str, Any],
    timeout: int,
    retries: int,
) -> tuple[int, int, dict[str, Any], str]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    url = f"{base_url.rstrip('/')}{endpoint}"
    started = time.perf_counter()
    last_status = 0
    last_raw = ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                duration_ms = int((time.perf_counter() - started) * 1000)
                parsed = json.loads(raw) if raw else {}
                return int(response.status), duration_ms, parsed, raw
        except urllib.error.HTTPError as exc:
            last_status = int(exc.code)
            last_raw = exc.read().decode("utf-8", errors="replace")
            if last_status != 429 or attempt >= retries:
                break
            time.sleep(min(20, 2**attempt * 3))
        except Exception as exc:
            last_status = 0
            last_raw = f"{type(exc).__name__}: {exc}"
            if attempt >= retries:
                break
            time.sleep(min(20, 2**attempt * 3))

    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        parsed = json.loads(last_raw) if last_raw else {}
    except json.JSONDecodeError:
        parsed = {}
    return last_status, duration_ms, parsed, last_raw


def record(
    results: list[Result],
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
    results.append(
        Result(
            timestamp=utc_now(),
            case_id=case_id,
            step=step,
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
        f"[{status}] {case_id} {step} http={http} duration_ms={duration_ms} "
        f"expected={compact(expected, 64)} actual={compact(actual, 96)}"
    )


def load_manifest(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("manifest must contain a non-empty cases array")

    cases: list[Case] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("each case must be an object")
        audio_path = Path(str(raw.get("audio_path") or ""))
        if not audio_path.is_absolute():
            audio_path = path.parent / audio_path
        cases.append(
            Case(
                case_id=str(raw["id"]),
                audio_path=audio_path,
                language=str(raw.get("language") or "ja"),
                expected_route=normalize_route(raw.get("expected_route")),
                expected_transcript=str(raw.get("expected_transcript") or ""),
                expected_facts=list(raw.get("expected_facts") or []),
                required_sources=[str(item) for item in raw.get("required_sources") or []],
            )
        )
    return cases


def run_case(args: argparse.Namespace, api_key: str, case: Case, results: list[Result]) -> None:
    if not case.audio_path.exists():
        record(
            results,
            case_id=case.case_id,
            step="audio_file",
            status="FAIL",
            http=0,
            duration_ms=0,
            language=case.language,
            expected="existing WAV file",
            actual=str(case.audio_path),
            notes="missing audio file",
        )
        return

    audio_b64 = base64.b64encode(case.audio_path.read_bytes()).decode("ascii")
    session_id = f"onsite-live-{args.timestamp}-{case.case_id}"

    http, duration_ms, stt, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/voice",
        body={
            "action": "speech_to_text",
            "audioData": audio_b64,
            "language": case.language,
            "sessionId": session_id,
        },
        timeout=args.timeout,
        retries=args.retries,
    )
    transcript = str(stt.get("transcript") or "").strip()
    provider = str(stt.get("sttProvider") or "")
    sim = similarity(case.expected_transcript, transcript) if case.expected_transcript else 1.0
    provider_ok = provider == "qwen-primary" or (
        args.allow_vosk_fallback and provider == "vosk-fallback"
    )
    if not (http == 200 and stt.get("success") is True and transcript):
        status = "FAIL"
    elif not provider_ok:
        status = "FAIL"
    elif duration_ms > args.stt_max_ms:
        status = "FAIL"
    elif sim < args.transcript_similarity:
        status = "WARN"
    elif duration_ms > args.stt_warn_ms:
        status = "WARN"
    else:
        status = "PASS"
    record(
        results,
        case_id=case.case_id,
        step="onsite_qwen_stt",
        status=status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=f"provider=qwen-primary latency<={args.stt_max_ms}ms",
        actual=(
            f"provider={provider or 'unknown'} similarity={sim:.3f} "
            f"transcript={compact(transcript)}"
        ),
        notes=compact(raw),
    )
    if not transcript:
        return

    time.sleep(args.sleep)
    http, duration_ms, chat, raw = post_json(
        base_url=args.host,
        api_key=api_key,
        endpoint="/api/chat",
        body={"query": transcript, "language": case.language, "session_id": session_id},
        timeout=args.timeout,
        retries=args.retries,
    )
    answer = str(chat.get("answer") or "").strip()
    metadata = chat.get("metadata") if isinstance(chat.get("metadata"), dict) else {}
    actual_route = response_route(chat)
    route_ok = actual_route == case.expected_route
    sources_ok, missing_sources = source_requirement_ok(metadata, case.required_sources)
    missing_facts = [
        fact
        for fact in case.expected_facts
        if not fact_in_answer(fact, answer, args.fact_similarity)
    ]
    if not (http == 200 and answer):
        status = "FAIL"
    elif not route_ok or not sources_ok or missing_facts:
        status = "FAIL"
    elif duration_ms > args.chat_warn_ms:
        status = "WARN"
    else:
        status = "PASS"
    record(
        results,
        case_id=case.case_id,
        step="live_langgraph_answer",
        status=status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=f"route={case.expected_route} sources={case.required_sources}",
        actual=(
            f"route={actual_route or 'unknown'} missing_sources={missing_sources} "
            f"missing_facts={missing_facts} answer={compact(answer)}"
        ),
        notes=compact(raw),
    )
    if not answer:
        return

    time.sleep(args.sleep)
    http, duration_ms, tts, raw = post_json(
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
        retries=args.retries,
    )
    audio = tts.get("audioResponse")
    if (
        http == 200
        and tts.get("success") is True
        and isinstance(audio, str)
        and len(audio) >= args.min_tts_audio_chars
        and duration_ms <= args.tts_max_ms
    ):
        status = "PASS"
    else:
        status = "FAIL"
    record(
        results,
        case_id=case.case_id,
        step="live_answer_tts",
        status=status,
        http=http,
        duration_ms=duration_ms,
        language=case.language,
        expected=f"{args.tts_provider} audio chars>={args.min_tts_audio_chars}",
        actual=(
            f"format={tts.get('audioFormat') or 'unknown'} "
            f"chars={len(audio) if isinstance(audio, str) else 0}"
        ),
        notes=compact(raw),
    )


def status_counts(results: list[Result]) -> dict[str, int]:
    return {
        "PASS": sum(1 for row in results if row.status == "PASS"),
        "WARN": sum(1 for row in results if row.status == "WARN"),
        "FAIL": sum(1 for row in results if row.status == "FAIL"),
    }


def write_reports(args: argparse.Namespace, cases: list[Case], results: list[Result]) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_md = output_dir / f"onsite-voice-live-proof-{args.timestamp}.md"
    report_csv = output_dir / f"onsite-voice-live-proof-{args.timestamp}.csv"

    with report_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(Result.__annotations__.keys()))
        writer.writeheader()
        for row in results:
            writer.writerow(row.__dict__)

    counts = status_counts(results)
    lines = [
        "# On-site Voice Live Proof",
        "",
        f"- Timestamp: {args.timestamp}",
        f"- Backend: {args.host}",
        f"- Manifest: {args.manifest}",
        f"- Cases: {len(cases)}",
        f"- Strict Qwen primary: {'no' if args.allow_vosk_fallback else 'yes'}",
        f"- Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL",
        f"- Detail CSV: {report_csv.name}",
        "",
        "## Scope",
        "",
        "- Audio files must be recorded on the real kiosk or target device microphone.",
        "- The runner calls the live `/api/voice` and `/api/chat` endpoints.",
        "- It gates Qwen-primary STT, LangGraph route/source/facts, and PiperPlus answer TTS.",
        "",
        "## Cases",
        "",
        "| Case | Language | Audio | Expected route |",
        "| --- | --- | --- | --- |",
    ]
    for case in cases:
        lines.append(
            f"| {case.case_id} | {case.language} | {case.audio_path} | {case.expected_route} |"
        )

    problem_rows = [row for row in results if row.status in {"WARN", "FAIL"}]
    if problem_rows:
        lines.extend(
            [
                "",
                "## Problems",
                "",
                "| Status | Case | Step | Expected | Actual | Notes |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in problem_rows[:100]:
            lines.append(
                f"| {row.status} | {row.case_id} | {row.step} | "
                f"{compact(row.expected)} | {compact(row.actual)} | {compact(row.notes)} |"
            )

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="On-site voice live proof runner.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--host", default=DEFAULT_URL)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=2.2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--stt-warn-ms", type=int, default=5000)
    parser.add_argument("--stt-max-ms", type=int, default=10000)
    parser.add_argument("--chat-warn-ms", type=int, default=15000)
    parser.add_argument("--tts-max-ms", type=int, default=15000)
    parser.add_argument("--transcript-similarity", type=float, default=0.50)
    parser.add_argument("--fact-similarity", type=float, default=0.60)
    parser.add_argument("--tts-provider", default="piper")
    parser.add_argument("--min-tts-audio-chars", type=int, default=64)
    parser.add_argument("--allow-vosk-fallback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_manifest(Path(args.manifest))
    if args.dry_run:
        print("Dry run: no live API calls will be executed.")
        print(f"Backend: {args.host}")
        print(f"Manifest: {args.manifest}")
        print(f"Cases: {len(cases)}")
        for case in cases:
            print(f"- {case.case_id}: {case.language} {case.expected_route} {case.audio_path}")
        return 0
    if not args.api_key:
        raise SystemExit("Error: --api-key is required")

    results: list[Result] = []
    for case in cases:
        run_case(args, args.api_key, case, results)
        if args.sleep > 0:
            time.sleep(args.sleep)
    write_reports(args, cases, results)
    counts = status_counts(results)
    print(f"Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
