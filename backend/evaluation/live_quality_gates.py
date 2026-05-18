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
import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

try:
    from backend.evaluation import live_quality_gate_suites as _quality_suites
    from backend.evaluation import live_quality_gate_utils as _quality_utils
except ImportError:  # pragma: no cover - supports `python -m evaluation...` from backend/
    from evaluation import live_quality_gate_suites as _quality_suites
    from evaluation import live_quality_gate_utils as _quality_utils

CASES_PATH = _quality_utils.CASES_PATH
DEFAULT_REPORTS_DIR = _quality_utils.DEFAULT_REPORTS_DIR
DEFAULT_URL = _quality_utils.DEFAULT_URL
EndpointPacer = _quality_utils.EndpointPacer
GateResult = _quality_utils.GateResult
compact = _quality_utils.compact
utc_now = _quality_utils.utc_now
run_m_suite = _quality_suites.run_m_suite
run_q_suite = _quality_suites.run_q_suite
run_t_suite = _quality_suites.run_t_suite


def __getattr__(name: str) -> Any:
    if hasattr(_quality_suites, name):
        return getattr(_quality_suites, name)
    return getattr(_quality_utils, name)


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
        "- q: LangGraph回答品質 "
        "(route / expected facts / prohibited claims / language / safety / live sources / latency)",
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
