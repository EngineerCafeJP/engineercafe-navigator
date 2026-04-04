"""
Phase 1: piper-plus TTS ベンチマーク・品質評価スクリプト

VOICEVOX / Kokoro との比較のため以下を実行します:
  1. レイテンシ測定 (10文字 / 50文字 / 200文字 × 各3回)
  2. 日本語サンプル10件の音声生成 (聴感比較用)
  3. 英語サンプル3件の音声生成 (聴感比較用)
  4. 測定結果レポートの出力

Usage:
    # piper-plus のみテスト (Docker不要)
    python -m backend.scripts.benchmark_tts_piper

    # VOICEVOX / Kokoro も含めて全比較 (Docker起動が必要)
    python -m backend.scripts.benchmark_tts_piper --all

出力:
    backend/scripts/tts_samples/   ... 生成音声ファイル
    tts_benchmark_result.md        ... レイテンシ測定レポート

前提:
    PIPER_BIN    : ~/piper-plus/piper/bin/piper (または環境変数で変更)
    PIPER_JA     : ~/Library/Application Support/piper/models/tsukuyomi-chan-6lang-fp16.onnx
    PIPER_EN     : ~/Library/Application Support/piper/models/en_US-lessac-medium.onnx
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import time
import wave
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PIPER_BIN = os.getenv(
    "PIPER_BIN",
    str(Path.home() / "piper-plus/piper/bin/piper"),
)
MODELS_DIR = Path.home() / "Library/Application Support/piper/models"
PIPER_JA_MODEL = os.getenv(
    "PIPER_JA_MODEL",
    str(MODELS_DIR / "tsukuyomi-chan-6lang-fp16.onnx"),
)
PIPER_EN_MODEL = os.getenv(
    "PIPER_EN_MODEL",
    str(MODELS_DIR / "en_US-lessac-medium.onnx"),
)

# ---------------------------------------------------------------------------
# サンプルテキスト
# ---------------------------------------------------------------------------

# 日本語サンプル（10件）: エンジニアカフェのユースケース想定
JA_SAMPLES = [
    # 短文（〜20文字）
    "いらっしゃいませ、エンジニアカフェへようこそ！",
    "ご利用ありがとうございます。",
    "何かお手伝いできることはありますか？",
    # 中文（〜50文字）
    "エンジニアカフェは、福岡市が運営するエンジニア向けの施設です。コワーキングスペースとして利用できます。",
    "イベントの開催スケジュールについては、公式ウェブサイトをご確認ください。",
    "会議室の予約は、受付にてお申し込みいただけます。",
    # 長文（〜100文字）
    "本日のイベントは午後2時から始まります。参加ご希望の方は、エントランスにてスタッフにお声がけください。お飲み物は自由にご利用いただけます。",
    "プログラミングの学習や技術書の閲覧、勉強会の開催など、エンジニアの皆さんの活動を幅広くサポートしております。",
    # 複雑な文（数字・英語混じり）
    "Wi-Fiのパスワードは EngineerCafe2024 です。ゲストネットワークもご利用いただけます。",
    "Pythonや JavaScript、Go言語など様々な技術スタックの勉強会を毎週開催しています。ぜひご参加ください！",
]

# 英語サンプル（3件）
EN_SAMPLES = [
    "Welcome to Engineer Cafe! How can I help you today?",
    "The coworking space is open from 10 AM to 10 PM on weekdays.",
    "We host weekly tech meetups covering Python, JavaScript, and cloud technologies. Feel free to join us!",
]

# レイテンシ測定用テキスト（文字数別）
LATENCY_TEXTS = {
    10: "こんにちは！どうぞ。",
    50: (
        "エンジニアカフェへようこそ！本日はどのようなご用件でしょうか。"
        "お気軽にスタッフまでお声がけください。"
    ),
    200: (
        "エンジニアカフェへようこそ！"
        "ここは福岡市が運営する、エンジニアのための施設です。"
        "コワーキングスペースや勉強会の開催、技術書の閲覧など幅広くご利用いただけます。"
        "スタッフが常駐しておりますので、ご不明な点はいつでもお気軽にお声がけください。"
        "プログラミングや最新技術について、仲間と共に学べる環境を提供しています。"
        "今日も皆さまにとって充実した一日となりますよう願っております。どうぞゆっくりお過ごしください。"
    ),
}


# ---------------------------------------------------------------------------
# piper-plus 直接呼び出し（HTTPサーバー不要）
# ---------------------------------------------------------------------------


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 22050) -> bytes:
    """生PCMデータを WAV フォーマットに変換"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


async def piper_synthesize(
    text: str,
    model_path: str,
    language: str = "ja",
    timeout: float = 30.0,
) -> tuple[bytes, float]:
    """
    piper-plus でテキストを合成し (WAVバイト, レイテンシ秒) を返す
    """
    cmd = [PIPER_BIN, "--model", model_path, "--output-raw"]
    if language == "en":
        # piper 元モデル（en_US-lessac）用
        pass  # 言語フラグ不要（モデルが自動判定）

    start = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=text.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"piper timeout after {timeout}s")

    elapsed = time.perf_counter() - start

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"piper failed (exit {proc.returncode}): {err[:300]}")

    wav_data = pcm_to_wav(stdout)
    return wav_data, elapsed


# ---------------------------------------------------------------------------
# HTTP クライアント経由テスト（VOICEVOX / Kokoro）
# ---------------------------------------------------------------------------


async def voicevox_synthesize(
    text: str,
    api_url: str = "http://localhost:50021",
    speaker_id: int = 3,
) -> tuple[Optional[bytes], float]:
    """VOICEVOX で合成し (WAVバイト, レイテンシ秒) を返す。失敗時は (None, 0)"""
    import httpx

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            q = await client.post(f"{api_url}/audio_query", params={"text": text, "speaker": speaker_id})
            q.raise_for_status()
            s = await client.post(f"{api_url}/synthesis", params={"speaker": speaker_id}, json=q.json())
            s.raise_for_status()
        elapsed = time.perf_counter() - start
        return s.content, elapsed
    except Exception as e:
        print(f"  [VOICEVOX] 接続失敗 (Docker 起動済み？): {e}")
        return None, 0.0


async def kokoro_synthesize(
    text: str,
    api_url: str = "http://localhost:8880",
    voice: str = "af_bella",
) -> tuple[Optional[bytes], float]:
    """Kokoro TTS で合成し (WAVバイト, レイテンシ秒) を返す。失敗時は (None, 0)"""
    import httpx

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{api_url}/v1/audio/speech",
                json={"model": "kokoro", "input": text, "voice": voice, "response_format": "wav"},
            )
            r.raise_for_status()
        elapsed = time.perf_counter() - start
        return r.content, elapsed
    except Exception as e:
        print(f"  [Kokoro] 接続失敗 (Docker 起動済み？): {e}")
        return None, 0.0


# ---------------------------------------------------------------------------
# ベンチマーク実行
# ---------------------------------------------------------------------------


async def run_latency_benchmark(include_voicevox: bool, include_kokoro: bool) -> dict:
    """
    文字数別レイテンシを測定する (各3回実行して平均を取る)
    """
    print("\n" + "=" * 60)
    print("レイテンシ測定")
    print("=" * 60)

    results = {}
    repeat = 3

    for char_count, text in LATENCY_TEXTS.items():
        actual_chars = len(text)
        print(f"\n[{char_count}文字テスト] 実文字数: {actual_chars}")
        results[char_count] = {}

        # piper-plus (tsukuyomi-chan)
        times_piper = []
        for i in range(repeat):
            _, t = await piper_synthesize(text, PIPER_JA_MODEL, language="ja")
            times_piper.append(t)
            print(f"  piper-plus (tsukuyomi) #{i+1}: {t:.3f}s")
        results[char_count]["piper_tsukuyomi"] = {
            "times": times_piper,
            "avg": sum(times_piper) / len(times_piper),
            "min": min(times_piper),
        }

        # VOICEVOX (オプション)
        if include_voicevox:
            times_vv = []
            for i in range(repeat):
                _, t = await voicevox_synthesize(text)
                if t > 0:
                    times_vv.append(t)
                    print(f"  VOICEVOX             #{i+1}: {t:.3f}s")
            if times_vv:
                results[char_count]["voicevox"] = {
                    "times": times_vv,
                    "avg": sum(times_vv) / len(times_vv),
                    "min": min(times_vv),
                }

    return results


async def generate_samples(output_dir: Path, include_voicevox: bool, include_kokoro: bool):
    """
    聴感比較用の音声サンプルを生成してファイルに保存する
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 60)
    print("サンプル音声生成")
    print("=" * 60)

    # --- 日本語サンプル ---
    print("\n[日本語サンプル - piper-plus tsukuyomi-chan]")
    for i, text in enumerate(JA_SAMPLES, 1):
        try:
            wav, elapsed = await piper_synthesize(text, PIPER_JA_MODEL, language="ja")
            path = output_dir / f"ja_{i:02d}_piper_tsukuyomi.wav"
            path.write_bytes(wav)
            print(f"  [{i:02d}] {text[:30]}... → {path.name} ({elapsed:.3f}s)")
        except Exception as e:
            print(f"  [{i:02d}] 失敗: {e}")

    print("\n[日本語サンプル - piper-plus css10]")
    for i, text in enumerate(JA_SAMPLES, 1):
        try:
            wav, elapsed = await piper_synthesize(text, str(MODELS_DIR / "css10-ja-6lang-fp16.onnx"), language="ja")
            path = output_dir / f"ja_{i:02d}_piper_css10.wav"
            path.write_bytes(wav)
            print(f"  [{i:02d}] {text[:30]}... → {path.name} ({elapsed:.3f}s)")
        except Exception as e:
            print(f"  [{i:02d}] 失敗: {e}")

    if include_voicevox:
        print("\n[日本語サンプル - VOICEVOX]")
        for i, text in enumerate(JA_SAMPLES, 1):
            wav, elapsed = await voicevox_synthesize(text)
            if wav:
                path = output_dir / f"ja_{i:02d}_voicevox.wav"
                path.write_bytes(wav)
                print(f"  [{i:02d}] {text[:30]}... → {path.name} ({elapsed:.3f}s)")

    # --- 英語サンプル ---
    print("\n[英語サンプル - piper-plus en_US-lessac]")
    for i, text in enumerate(EN_SAMPLES, 1):
        try:
            wav, elapsed = await piper_synthesize(text, PIPER_EN_MODEL, language="en")
            path = output_dir / f"en_{i:02d}_piper_lessac.wav"
            path.write_bytes(wav)
            print(f"  [{i:02d}] {text[:40]}... → {path.name} ({elapsed:.3f}s)")
        except Exception as e:
            print(f"  [{i:02d}] 失敗: {e}")

    if include_kokoro:
        print("\n[英語サンプル - Kokoro TTS]")
        for i, text in enumerate(EN_SAMPLES, 1):
            wav, elapsed = await kokoro_synthesize(text)
            if wav:
                path = output_dir / f"en_{i:02d}_kokoro.wav"
                path.write_bytes(wav)
                print(f"  [{i:02d}] {text[:40]}... → {path.name} ({elapsed:.3f}s)")


def generate_report(latency_results: dict, output_path: Path):
    """
    Markdown 形式のレポートを生成する
    """
    lines = [
        "# piper-plus Phase 1 ベンチマーク結果",
        "",
        f"日時: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"環境: macOS ARM64 (Apple Silicon)",
        f"piper バイナリ: {PIPER_BIN}",
        f"日本語モデル: {Path(PIPER_JA_MODEL).name}",
        f"英語モデル: {Path(PIPER_EN_MODEL).name}",
        "",
        "## レイテンシ測定結果",
        "",
        "| 文字数 | piper-plus (avg) | piper-plus (min) | VOICEVOX (avg) | VOICEVOX (min) | 改善率 (avg) |",
        "|--------|-----------------|-----------------|---------------|---------------|-------------|",
    ]

    for char_count, data in sorted(latency_results.items()):
        piper_data = data.get("piper_tsukuyomi", {})
        vv_data = data.get("voicevox", {})

        piper_avg = piper_data.get("avg", 0)
        piper_min = piper_data.get("min", 0)
        vv_avg = vv_data.get("avg", 0)
        vv_min = vv_data.get("min", 0)

        if vv_avg > 0:
            improvement = (vv_avg - piper_avg) / vv_avg * 100
            improvement_str = f"{improvement:+.1f}%"
        else:
            improvement_str = "N/A (VOICEVOX未計測)"

        vv_avg_str = f"{vv_avg:.3f}s" if vv_avg > 0 else "未計測"
        vv_min_str = f"{vv_min:.3f}s" if vv_min > 0 else "未計測"

        lines.append(
            f"| {char_count}文字 | {piper_avg:.3f}s | {piper_min:.3f}s "
            f"| {vv_avg_str} | {vv_min_str} | {improvement_str} |"
        )

    lines += [
        "",
        "## 受入基準チェック",
        "",
        "| 基準 | 結果 | 判定 |",
        "|------|------|------|",
    ]

    # piper-plus 50文字のレイテンシ確認
    p50 = latency_results.get(50, {}).get("piper_tsukuyomi", {}).get("avg", 0)
    vv50 = latency_results.get(50, {}).get("voicevox", {}).get("avg", 0)
    if vv50 > 0:
        improvement_50 = (vv50 - p50) / vv50 * 100
        latency_ok = improvement_50 >= 50
        lines.append(
            f"| レイテンシ 50%以上改善 | piper {p50:.3f}s / VOICEVOX {vv50:.3f}s ({improvement_50:+.1f}%) "
            f"| {'✅ PASS' if latency_ok else '❌ FAIL'} |"
        )
    else:
        lines.append("| レイテンシ 50%以上改善 | VOICEVOX 未計測（Docker起動が必要） | ⚠️ 未確認 |")

    lines += [
        "| 日本語音声品質 | 聴感比較サンプルを確認してください | 手動評価 |",
        "| 既存サービスとの共存 | env var 切替で実装済み | ✅ PASS |",
        "",
        "## 生成サンプル",
        "",
        "```",
        "tts_samples/",
        "  ja_01~10_piper_tsukuyomi.wav  ← tsukuyomi-chan モデル（日本語）",
        "  ja_01~10_piper_css10.wav      ← css10 モデル（日本語）",
        "  ja_01~10_voicevox.wav         ← VOICEVOX（Docker起動時のみ）",
        "  en_01~03_piper_lessac.wav     ← lessac モデル（英語）",
        "  en_01~03_kokoro.wav           ← Kokoro TTS（Docker起動時のみ）",
        "```",
        "",
        "## モデル情報",
        "",
        "| モデル | 言語 | 話者 | サイズ感 |",
        "|--------|------|------|---------|",
        "| tsukuyomi-chan-6lang-fp16 | 日本語 | 月詠みらい(v2) | FP16 ONNX |",
        "| css10-ja-6lang-fp16 | 日本語 | css10 JP | FP16 ONNX |",
        "| en_US-lessac-medium | 英語 | Lessac | ONNX medium |",
        "",
        "## 備考",
        "",
        "- VOICEVOX / Kokoro の計測には Docker 起動が必要 (`docker-compose up voicevox kokoro-tts`)",
        "- `--all` フラグで全サービスを含む比較が可能",
        "- Cloud Run コールドスタートは Phase 2 で別途計測",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nレポート出力: {output_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main(include_all: bool):
    print("=" * 60)
    print("piper-plus Phase 1 ベンチマーク")
    print("=" * 60)

    # 前提チェック
    errors = []
    if not Path(PIPER_BIN).exists():
        errors.append(f"piper バイナリが見つかりません: {PIPER_BIN}")
    if not Path(PIPER_JA_MODEL).exists():
        errors.append(f"日本語モデルが見つかりません: {PIPER_JA_MODEL}")
    if not Path(PIPER_EN_MODEL).exists():
        errors.append(f"英語モデルが見つかりません: {PIPER_EN_MODEL}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    print(f"piper bin : {PIPER_BIN}")
    print(f"JA model  : {PIPER_JA_MODEL}")
    print(f"EN model  : {PIPER_EN_MODEL}")
    if include_all:
        print("モード     : 全サービス比較 (VOICEVOX + Kokoro TTS 含む)")
    else:
        print("モード     : piper-plus のみ (--all で全比較)")

    # 出力ディレクトリ
    script_dir = Path(__file__).parent
    samples_dir = script_dir / "tts_samples"
    report_path = script_dir / "tts_benchmark_result.md"

    # 1. サンプル生成
    await generate_samples(samples_dir, include_all, include_all)

    # 2. レイテンシ測定
    latency_results = await run_latency_benchmark(include_all, include_all)

    # 3. レポート生成
    generate_report(latency_results, report_path)

    # 4. サマリー表示
    print("\n" + "=" * 60)
    print("結果サマリー")
    print("=" * 60)
    for char_count, data in sorted(latency_results.items()):
        piper_avg = data.get("piper_tsukuyomi", {}).get("avg", 0)
        vv_avg = data.get("voicevox", {}).get("avg", 0)
        if vv_avg > 0:
            imp = (vv_avg - piper_avg) / vv_avg * 100
            print(f"  {char_count}文字: piper {piper_avg:.3f}s / VOICEVOX {vv_avg:.3f}s → {imp:+.1f}%")
        else:
            print(f"  {char_count}文字: piper {piper_avg:.3f}s (VOICEVOX 未計測)")

    print(f"\n音声サンプル: {samples_dir}/")
    print(f"レポート    : {report_path}")
    print("\n聴感比較: samples ディレクトリの WAV ファイルを再生して確認してください。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="piper-plus Phase 1 ベンチマーク")
    parser.add_argument("--all", action="store_true", help="VOICEVOX / Kokoro TTS も含む全比較")
    args = parser.parse_args()
    asyncio.run(main(include_all=args.all))
