#!/usr/bin/env bash
# Engineer Cafe Navigator — voice fixture regenerator.
# Not executed by CI. Only run manually on intentional fixture change.
# See README.md for provenance and rationale.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/sample.wav"
PHRASE="tell me about engineer cafe"

if ! command -v say >/dev/null 2>&1; then
  echo "error: macOS 'say' command is required (primary path)" >&2
  echo "hint: use the piper fallback documented in README.md" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg is required" >&2
  exit 1
fi
if ! command -v shasum >/dev/null 2>&1; then
  echo "error: shasum is required" >&2
  exit 1
fi

TMP_AIFF="$(mktemp -t ecn-voice-sample.XXXXXX).aiff"
cleanup() { rm -f "$TMP_AIFF"; }
trap cleanup EXIT

say -v Samantha -o "$TMP_AIFF" "$PHRASE"

ffmpeg -y -i "$TMP_AIFF" \
  -ar 16000 -ac 1 -sample_fmt s16 \
  "$OUT" >/dev/null 2>&1

echo "generated: $OUT"
ls -la "$OUT"
shasum -a 256 "$OUT"
echo "Update the sha256 row in README.md if this differs from the recorded value."
