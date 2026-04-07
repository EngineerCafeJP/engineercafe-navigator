"""piper-plus サンプル音声生成スクリプト

piper-tts-plus Python SDK（server.py と同一方式）で
tts_samples_piper/ 配下に日本語・英語サンプルを生成します。
既存の tts_samples/ は変更しません。

Usage:
    python -m backend.scripts.generate_tts_samples
"""

from __future__ import annotations

import io
import os
import wave
from pathlib import Path

from huggingface_hub import snapshot_download
from piper import PiperVoice

# ---------------------------------------------------------------------------
# 設定（server.py と同じデフォルト値）
# ---------------------------------------------------------------------------

MODEL_REPO = os.getenv("PIPER_MODEL_REPO", "ayousanz/piper-plus-tsukuyomi-chan")
MODEL_DIR = Path(os.getenv("PIPER_MODEL_DIR", str(Path.home() / ".cache/piper")))
SPEED = float(os.getenv("PIPER_SPEED", "0.65"))  # 1.0=標準, <1.0=遅い

OUT_DIR = Path(__file__).parent / "tts_samples_piper"

# ---------------------------------------------------------------------------
# サンプルテキスト
# ---------------------------------------------------------------------------

JA_SAMPLES = [
    "いらっしゃいませ、エンジニアカフェへようこそ！",
    "ご利用ありがとうございます。",
    "何かお手伝いできることはありますか？",
    "エンジニアカフェは、福岡市が運営するエンジニア向けの施設です。コワーキングスペースとして利用できます。",
    "イベントの開催スケジュールについては、公式ウェブサイトをご確認ください。",
    "会議室の予約は、受付にてお申し込みいただけます。",
    "本日のイベントは午後2時から始まります。参加ご希望の方は、エントランスにてスタッフにお声がけください。お飲み物は自由にご利用いただけます。",
    "プログラミングの学習や技術書の閲覧、勉強会の開催など、エンジニアの皆さんの活動を幅広くサポートしております。",
    "Wi-Fiのパスワードは EngineerCafe2024 です。ゲストネットワークもご利用いただけます。",
    "Pythonや JavaScript、Go言語など様々な技術スタックの勉強会を毎週開催しています。"
    "ぜひご参加ください！",
]

EN_SAMPLES = [
    "Welcome to Engineer Cafe! How can I help you today?",
    "The coworking space is open from 10 AM to 10 PM on weekdays.",
    "We host weekly tech meetups covering Python, JavaScript, and cloud technologies. "
    "Feel free to join us!",
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def load_voice() -> PiperVoice:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Checking model: {MODEL_REPO}")
    snapshot_download(repo_id=MODEL_REPO, local_dir=MODEL_DIR, local_dir_use_symlinks=False)
    model_paths = sorted(MODEL_DIR.rglob("*.onnx"))
    if not model_paths:
        raise RuntimeError(f"No ONNX model found in {MODEL_DIR}")
    print(f"Loading model : {model_paths[0]}")
    return PiperVoice.load(str(model_paths[0]))


def resolve_language_id(voice: PiperVoice, language: str) -> int | None:
    language_map = getattr(voice.config, "language_id_map", None) or {}
    return language_map.get(language)


def synthesize(voice: PiperVoice, text: str, language: str, speed: float) -> bytes:
    length_scale = 1.0 / max(0.5, min(2.0, speed))
    language_id = resolve_language_id(voice, language)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize(
            text,
            wav_file,
            length_scale=length_scale,
            noise_scale=0.667,
            language_id=language_id,
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    voice = load_voice()
    language_map = getattr(voice.config, "language_id_map", None) or {}

    print()
    print(f"sample_rate    : {voice.config.sample_rate}")
    print(f"speed          : {SPEED}  (length_scale={1.0 / SPEED:.3f})")
    print(f"language_map   : {language_map}")
    print(f"output dir     : {OUT_DIR}")
    print()

    # --- 日本語サンプル ---
    print("=== 日本語サンプル (tsukuyomi, speed=0.65) ===")
    for i, text in enumerate(JA_SAMPLES, 1):
        out_path = OUT_DIR / f"ja_{i:02d}_piper_tsukuyomi.wav"
        print(f"  [{i:02d}/10] {text[:30]}...")
        wav = synthesize(voice, text, "ja", SPEED)
        out_path.write_bytes(wav)
        print(f"         -> {out_path.name} ({len(wav):,} bytes)")

    print()

    # --- 英語サンプル ---
    print("=== 英語サンプル (tsukuyomi, speed=0.65) ===")
    for i, text in enumerate(EN_SAMPLES, 1):
        out_path = OUT_DIR / f"en_{i:02d}_piper_tsukuyomi.wav"
        print(f"  [{i:02d}/03] {text[:50]}...")
        wav = synthesize(voice, text, "en", SPEED)
        out_path.write_bytes(wav)
        print(f"         -> {out_path.name} ({len(wav):,} bytes)")

    print()
    print("完了。生成ファイル一覧:")
    for f in sorted(OUT_DIR.glob("*.wav")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
