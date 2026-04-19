#!/usr/bin/env python3
"""Frontend latency probe for pre-field verification.

Measures user-path latency on the deployed frontend and writes both JSON and
Markdown summaries so they can be attached to a workflow run.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://frontend-delta-six-20.vercel.app"


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None


PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec(
        name="qa_answer",
        method="POST",
        path="/api/qa",
        payload={
            "action": "ask",
            "question": "営業時間を教えてください",
            "text": "営業時間を教えてください",
            "language": "ja",
            "sessionId": "latency-probe",
            "visitorId": "latency-probe",
        },
    ),
    ProbeSpec(
        name="tts_roundtrip",
        method="POST",
        path="/api/voice",
        payload={
            "action": "text_to_speech",
            "text": "テストです",
            "language": "ja",
            "includeVrmControl": True,
            "sessionId": "latency-probe",
        },
    ),
    ProbeSpec(
        name="character_status",
        method="POST",
        path="/api/character",
        payload={"action": "get_status"},
    ),
)


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        raise ValueError("values must not be empty")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def request_json(base_url: str, spec: ProbeSpec, timeout: float) -> tuple[float, int, Any]:
    body_bytes = None
    headers = {"Content-Type": "application/json"}
    if spec.payload is not None:
        body_bytes = json.dumps(spec.payload).encode("utf-8")

    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}{spec.path}",
        data=body_bytes,
        headers=headers,
        method=spec.method,
    )

    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read()
        elapsed_ms = (time.perf_counter() - started) * 1000
        payload = json.loads(response_body.decode("utf-8"))
        return elapsed_ms, response.status, payload


def validate_response(spec: ProbeSpec, status_code: int, payload: Any) -> None:
    if status_code != 200:
        raise RuntimeError(f"{spec.name}: unexpected status {status_code}")

    if not isinstance(payload, dict):
        raise RuntimeError(f"{spec.name}: response is not an object")

    if payload.get("success") is False:
        raise RuntimeError(f"{spec.name}: success=false response: {payload}")

    if spec.name == "tts_roundtrip" and not payload.get("audioResponse"):
        raise RuntimeError(f"{spec.name}: audioResponse missing")


def run_probe(
    base_url: str,
    iterations: int,
    timeout: float,
) -> dict[str, Any]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results: list[dict[str, Any]] = []

    for spec in PROBES:
        samples: list[float] = []
        failures: list[str] = []

        for _ in range(iterations):
            try:
                elapsed_ms, status_code, payload = request_json(base_url, spec, timeout)
                validate_response(spec, status_code, payload)
                samples.append(round(elapsed_ms, 2))
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
                failures.append(str(exc))

        if samples:
            summary = {
                "samples_ms": samples,
                "count": len(samples),
                "failures": failures,
                "p50_ms": round(percentile(samples, 0.50), 2),
                "p95_ms": round(percentile(samples, 0.95), 2),
                "p99_ms": round(percentile(samples, 0.99), 2),
                "mean_ms": round(statistics.mean(samples), 2),
                "max_ms": round(max(samples), 2),
            }
        else:
            summary = {
                "samples_ms": [],
                "count": 0,
                "failures": failures,
            }

        results.append(
            {
                "name": spec.name,
                "method": spec.method,
                "path": spec.path,
                **summary,
            }
        )

    return {
        "base_url": base_url,
        "iterations": iterations,
        "timeout_seconds": timeout,
        "started_at": started_at,
        "results": results,
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frontend Latency Probe",
        "",
        f"- Base URL: `{report['base_url']}`",
        f"- Iterations: `{report['iterations']}`",
        f"- Timeout: `{report['timeout_seconds']}` seconds",
        f"- Started At (UTC): `{report['started_at']}`",
        "",
        "| Probe | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | max (ms) | failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in report["results"]:
        lines.append(
            "| {name} | {p50} | {p95} | {p99} | {mean} | {max_} | {failures} |".format(
                name=result["name"],
                p50=result.get("p50_ms", "-"),
                p95=result.get("p95_ms", "-"),
                p99=result.get("p99_ms", "-"),
                mean=result.get("mean_ms", "-"),
                max_=result.get("max_ms", "-"),
                failures=len(result.get("failures", [])),
            )
        )

    lines.append("")
    for result in report["results"]:
        failures = result.get("failures", [])
        if failures:
            lines.append(f"## {result['name']} failures")
            lines.extend(f"- {failure}" for failure in failures)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure deployed frontend latency.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/latency-probe.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/latency-probe.md"))
    return parser.parse_args()


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    report = run_probe(args.base_url, args.iterations, args.timeout)
    markdown = format_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    write_output(args.json_out, json_text)
    write_output(args.markdown_out, markdown)

    print(markdown)

    has_failure = any(result.get("failures") for result in report["results"])
    return 1 if has_failure else 0


if __name__ == "__main__":
    sys.exit(main())
