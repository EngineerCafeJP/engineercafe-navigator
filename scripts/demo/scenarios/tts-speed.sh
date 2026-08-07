#!/usr/bin/env bash
# S3: TTS 話速検証 — piper-plus の PIPER_SPEED(length_scale) が合成 WAV の長さに効いているか
#
# 背景: docker/piper-plus/server.py は PIPER_SPEED 環境変数を読んでいないため、
#       Piper デフォルト速度(length_scale=1.0)で合成される = 英語が速すぎる。
#       clients.py のコメント（"PIPER_SPEED でサーバー側に設定済み"）と実装が乖離。
#
# 検証方法:
#   同一テキストを /synthesize に speed パラメータを変えて合成し、
#   WAV duration を比較する。
#     - 修正前: サーバーが speed を無視 → duration が変わらない (RED)
#     - 修正後: length_scale = 1/speed が適用 → duration が伸びる (GREEN)
#
# 使い方: bash scripts/demo/scenarios/tts-speed.sh
# 結果: docs/demo/coscup2026/evidence/scenario/tts-speed/ に保存
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "${REPO_ROOT}"

PIPER_URL="${DEMO_PIPER_URL:-http://localhost:8090}"
EVIDENCE_DIR="${DEMO_EVIDENCE_DIR:-docs/demo/coscup2026/evidence/scenario/tts-speed}"
mkdir -p "${EVIDENCE_DIR}"

TEXT="Welcome to Engineer Cafe! You can work in the main hall, use the free Wi-Fi, and explore the latest technology on the first floor."
SPEEDS=(1.0 0.8 0.65)

synth_duration() {
  # $1=speed -> stdout: WAV duration(秒)
  # 注意: speed は必ず明示送信する（未送信だとサーバーは PIPER_SPEED env を
  # 適用するため、speed=1.0 と env=0.65 が混同して判定が狂う）
  local speed="$1"
  local wav_file="${EVIDENCE_DIR}/speed_${speed}.wav"
  curl -fsS --max-time 60 -X POST "${PIPER_URL}/synthesize" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"text":sys.argv[1],"language":"en","speed":float(sys.argv[2])}))' "${TEXT}" "${speed}")" \
    -o "${wav_file}"
  python3 - "${wav_file}" <<'PY'
import sys, wave
w = wave.open(sys.argv[1], "rb")
print(f"{w.getnframes() / w.getframerate():.3f}")
PY
}

echo "[tts-speed] Piper: ${PIPER_URL}"
echo "[tts-speed] Text: ${TEXT:0:60}... (${#TEXT} chars)"
echo ""

durations=()
for speed in "${SPEEDS[@]}"; do
  duration=$(synth_duration "${speed}")
  durations+=("${duration}")
  echo "[tts-speed] speed=${speed} -> duration=${duration}s"
done

d1="${durations[0]}"
d2="${durations[1]}"
d3="${durations[2]}"

# 判定: 0.65 で duration が 1.0 より 20% 以上長ければ length_scale が効いている
has_speed_control=$(python3 - "${d1}" "${d3}" <<'PY'
import sys
base, slow = float(sys.argv[1]), float(sys.argv[2])
print("true" if slow > base * 1.2 else "false")
PY
)

{
  echo "=== S3 tts-speed: $(date) ==="
  echo "text=${TEXT}"
  printf "speed_1.0_duration=%ss\n" "${d1}"
  printf "speed_0.8_duration=%ss\n" "${d2}"
  printf "speed_0.65_duration=%ss\n" "${d3}"
  echo "length_scale_effective=${has_speed_control}"
} | tee "${EVIDENCE_DIR}/result.txt"

if [ "${has_speed_control}" = "true" ]; then
  echo ""
  echo "[tts-speed] PASS: speed 0.65 で duration が延長 → length_scale が有効"
  exit 0
else
  echo ""
  echo "[tts-speed] FAIL: speed パラメータが無視されている → PIPER_SPEED 未実装 (RED)"
  exit 1
fi
