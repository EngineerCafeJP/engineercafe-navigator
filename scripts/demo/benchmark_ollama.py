#!/usr/bin/env python3
"""COSCUP 2026 デモ用 Ollama モデル ベンチマークスクリプト.

ホスト上の Ollama (Metal GPU) に対して、デモ想定質問 2〜3 個を
RAG コンテキスト込みで投げ、以下をモデル別に計測する。

- TTFT (time to first token): ストリーミング開始〜最初の content チャンク
- 完答時間: リクエスト開始〜全文受信
- 回答本文 (品質レビュー用に保存)

使い方:
    python3 scripts/demo/benchmark_ollama.py \
        --models qwen3.6:35b gemma4:e4b gemma4:e2b qwen3.5:9b qwen3:8b \
        --out docs/demo/coscup2026/evidence/benchmark

前提: Ollama が http://localhost:11434 で起動していること。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

OLLAMA_BASE_URL = "http://localhost:11434/v1"

SYSTEM_PROMPT = (
    "You are the reception assistant of Engineer Cafe in Fukuoka, Japan. "
    "Answer in English. Keep your answer to 2-3 short sentences. "
    "Base your answer only on the provided information."
)

# RAG コンテキストは backend/knowledge/data/*.yaml の content_en を参照する
DEMO_QUESTIONS: list[dict[str, str]] = [
    {
        "name": "q1_what_can_i_do",
        "question": "What can I do at Engineer Cafe?",
        "context": (
            "The 1F Main Hall serves as both an event space and a coworking area. "
            "Events take priority; when no events are scheduled, it is open for coworking. "
            "30 free seats with free Wi-Fi and power strips at every seat. "
            "4K monitor rental and engineering book library available. "
            "Latest tech: Apple Vision Pro, Meta Quest, mocopi motion capture, Tello drone, HHKB try station. "
            "Equipment is typically used at events but individual demos may be possible with a Community Manager. "
            "The B1F MAKER's Space is a fabrication lab with 3D printers, laser cutter, and other tools. "
            "2F has paid meeting rooms managed by Akarenga Hall. "
            "Drinks, a water server, and vending machines are available."
        ),
    },
    {
        "name": "q2_where_is_toilet",
        "question": "Where is the toilet?",
        "context": (
            "The restrooms are located at the back of the terrace on the 1F. "
            "Important route: you cannot reach the restrooms directly from inside the building. "
            "Go through the passage behind the reception desk to the terrace, "
            "then to the restrooms at the far end of the terrace. "
            "Western-style toilets with warm-water bidets are available. "
            "There is no dedicated diaper-changing space."
        ),
    },
    {
        "name": "q3_cafe_open_weekend",
        "question": "Is the cafe open on weekends?",
        "context": (
            "Cafe and bar SAINO opening hours: weekdays Day Time 12:00-17:00 and Night Time 18:00-20:00. "
            "Open days: Tuesday, Thursday, Friday, Saturday, and Sunday."
        ),
    },
]


def _time_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def _warm_up(client: httpx.AsyncClient, model: str) -> int:
    """モデルを Metal にロードするためのウォームアップ要求。ロード時間を返す."""
    started = time.perf_counter()
    await client.post(
        f"{OLLAMA_BASE_URL}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Say OK."}],
            "stream": False,
            "max_tokens": 4,
        },
        timeout=600.0,
    )
    return _time_ms(started)


async def _run_question(
    client: httpx.AsyncClient,
    model: str,
    question: dict[str, str],
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Information:\n{question['context']}\n\n"
                f"Question: {question['question']}"
            ),
        },
    ]
    request_started = time.perf_counter()
    ttft_ms: int | None = None
    chunks: list[str] = []
    reasoning_chars = 0
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None

    async with client.stream(
        "POST",
        f"{OLLAMA_BASE_URL}/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 1024,
            "temperature": 0.7,
            # Qwen3 系の thinking モードを無効化（gemma4 等では無視される）
            "reasoning_effort": "none",
            "think": False,
        },
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content and ttft_ms is None:
                    ttft_ms = _time_ms(request_started)
                if content:
                    chunks.append(content)
                reasoning_chars += len(delta.get("reasoning_content") or "")
                finish_reason = choices[0].get("finish_reason") or finish_reason
            if chunk.get("usage"):
                usage = chunk["usage"]

    total_ms = _time_ms(request_started)
    return {
        "name": question["name"],
        "question": question["question"],
        "ttft_ms": ttft_ms if ttft_ms is not None else -1,
        "total_ms": total_ms,
        "finish_reason": finish_reason,
        "reasoning_chars": reasoning_chars,
        "usage": usage,
        "answer": "".join(chunks),
    }


async def _benchmark_model(
    model: str,
    questions: list[dict[str, str]],
    out_dir: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {"model": model, "questions": []}
    async with httpx.AsyncClient(timeout=600.0) as client:
        load_ms = await _warm_up(client, model)
        results["load_ms"] = load_ms
        for question in questions:
            result = await _run_question(client, model, question)
            results["questions"].append(result)
            print(
                f"  [{model}] {result['name']}: ttft={result['ttft_ms']}ms "
                f"total={result['total_ms']}ms"
            )
            print(f"      answer: {result['answer'][:200]!r}")
    (out_dir / f"{model.replace('/', '_')}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen3.6:35b", "gemma4:e4b", "gemma4:e2b", "qwen3.5:9b", "qwen3:8b"],
    )
    parser.add_argument(
        "--out",
        default="docs/demo/coscup2026/evidence/benchmark",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Benchmarking {len(args.models)} models: {', '.join(args.models)}")
    print(f"Output: {out_dir.resolve()}")
    all_results = []
    for model in args.models:
        print(f"\n=== model: {model} ===")
        all_results.append(await _benchmark_model(model, DEMO_QUESTIONS, out_dir))

    print("\n=== SUMMARY (warm, RAG context included) ===")
    header = f"{'model':<16} {'load_ms':>8} " + " ".join(
        f"{q['name']:<14}" for q in DEMO_QUESTIONS
    )
    print(f"{'':<16} {'':>8} " + " ".join(f"{'ttft/total':>14}" for _ in DEMO_QUESTIONS))
    for model, result in zip(args.models, all_results, strict=False):
        cells = []
        for q in result["questions"]:
            cells.append(f"{q['ttft_ms']}/{q['total_ms']}")
        print(
            f"{model:<16} {result['load_ms']:>8} " + " ".join(f"{c:>14}" for c in cells)
        )

    summary = {
        "models": [
            {
                "model": r["model"],
                "load_ms": r["load_ms"],
                "questions": [
                    {"name": q["name"], "ttft_ms": q["ttft_ms"], "total_ms": q["total_ms"]}
                    for q in r["questions"]
                ],
            }
            for r in all_results
        ]
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved summary + per-model JSON to {out_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
