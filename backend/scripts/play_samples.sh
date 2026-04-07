#!/bin/bash
# 生成サンプルを順番に再生して聴感評価するスクリプト
#
# Usage:
#   ./play_samples.sh            # 全サンプルを順番に再生
#   ./play_samples.sh ja         # 日本語サンプルのみ
#   ./play_samples.sh en         # 英語サンプルのみ
#   ./play_samples.sh compare 1  # サンプル番号1の全モデルを比較再生

SAMPLES_DIR="$(dirname "$0")/tts_samples"

if [ ! -d "$SAMPLES_DIR" ]; then
    echo "ERROR: tts_samples/ が見つかりません。先にベンチマークを実行してください。"
    echo "  python -m backend.scripts.benchmark_tts_piper"
    exit 1
fi

play_file() {
    local file="$1"
    local label="$2"
    echo ""
    echo "▶ $label"
    echo "  ファイル: $(basename $file)"
    afplay "$file"
}

case "${1:-all}" in
    ja)
        echo "=== 日本語サンプル比較 ==="
        for i in $(seq -w 1 10); do
            tsuku="$SAMPLES_DIR/ja_${i}_piper_tsukuyomi.wav"
            css10="$SAMPLES_DIR/ja_${i}_piper_css10.wav"
            vvox="$SAMPLES_DIR/ja_${i}_voicevox.wav"

            [ -f "$tsuku" ] && play_file "$tsuku" "[${i}] piper tsukuyomi-chan"
            [ -f "$css10" ] && play_file "$css10" "[${i}] piper css10"
            [ -f "$vvox"  ] && play_file "$vvox"  "[${i}] VOICEVOX"

            echo "  ---"
            read -p "  次へ進む（Enter）/ 終了（q+Enter）: " input
            [ "$input" = "q" ] && break
        done
        ;;

    en)
        echo "=== 英語サンプル比較 ==="
        for i in $(seq -w 1 3); do
            lessac="$SAMPLES_DIR/en_${i}_piper_lessac.wav"
            kokoro="$SAMPLES_DIR/en_${i}_kokoro.wav"

            [ -f "$lessac" ] && play_file "$lessac" "[${i}] piper en_US-lessac"
            [ -f "$kokoro" ] && play_file "$kokoro" "[${i}] Kokoro TTS"

            echo "  ---"
            read -p "  次へ進む（Enter）/ 終了（q+Enter）: " input
            [ "$input" = "q" ] && break
        done
        ;;

    compare)
        NUM="${2:-01}"
        NUM=$(printf "%02d" $NUM)
        echo "=== サンプル #${NUM} 全モデル比較 ==="

        for f in "$SAMPLES_DIR"/ja_${NUM}_*.wav "$SAMPLES_DIR"/en_${NUM}_*.wav; do
            [ -f "$f" ] || continue
            label=$(basename "$f" .wav | sed 's/^[a-z][a-z]_[0-9]*_//')
            play_file "$f" "$label"
            sleep 0.3
        done
        ;;

    all|*)
        echo "=== 全サンプル再生 ==="
        echo "ファイル数: $(ls "$SAMPLES_DIR"/*.wav 2>/dev/null | wc -l | tr -d ' ')"
        echo ""

        echo "--- 日本語 (tsukuyomi-chan) ---"
        for f in "$SAMPLES_DIR"/ja_*_piper_tsukuyomi.wav; do
            [ -f "$f" ] || continue
            play_file "$f" "$(basename $f .wav)"
        done

        echo ""
        echo "--- 日本語 (css10) ---"
        for f in "$SAMPLES_DIR"/ja_*_piper_css10.wav; do
            [ -f "$f" ] || continue
            play_file "$f" "$(basename $f .wav)"
        done

        if ls "$SAMPLES_DIR"/ja_*_voicevox.wav 2>/dev/null | grep -q .; then
            echo ""
            echo "--- 日本語 (VOICEVOX) ---"
            for f in "$SAMPLES_DIR"/ja_*_voicevox.wav; do
                play_file "$f" "$(basename $f .wav)"
            done
        fi

        echo ""
        echo "--- 英語 (piper lessac) ---"
        for f in "$SAMPLES_DIR"/en_*_piper_lessac.wav; do
            [ -f "$f" ] || continue
            play_file "$f" "$(basename $f .wav)"
        done

        if ls "$SAMPLES_DIR"/en_*_kokoro.wav 2>/dev/null | grep -q .; then
            echo ""
            echo "--- 英語 (Kokoro TTS) ---"
            for f in "$SAMPLES_DIR"/en_*_kokoro.wav; do
                play_file "$f" "$(basename $f .wav)"
            done
        fi
        ;;
esac

echo ""
echo "再生完了"
