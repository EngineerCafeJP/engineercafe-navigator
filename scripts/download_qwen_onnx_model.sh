#!/usr/bin/env bash
set -euo pipefail

# Download the Daumee/Qwen3-ASR-0.6B-ONNX-CPU artifact layout used by the
# experimental Cloud Run ONNX candidate revision.

TARGET_DIR="${1:-${QWEN_ONNX_MODEL_DIR:-models/qwen3-asr-0.6b-onnx}}"
REPO="${QWEN_ONNX_HF_REPO:-Daumee/Qwen3-ASR-0.6B-ONNX-CPU}"
REVISION="${QWEN_ONNX_REVISION:-main}"
BASE_URL="https://huggingface.co/${REPO}/resolve/${REVISION}"

download_file() {
  local relative_path="$1"
  local output_relative_path="${2:-$relative_path}"
  local output_path="${TARGET_DIR}/${output_relative_path}"
  local output_dir
  output_dir="$(dirname "$output_path")"
  mkdir -p "$output_dir"

  if [ -s "$output_path" ]; then
    echo "Already present: $relative_path"
    return
  fi

  echo "Downloading: $relative_path"
  curl --fail --location --retry 5 --retry-delay 2 --continue-at - \
    "${BASE_URL}/${relative_path}" \
    --output "$output_path"
}

mkdir -p "$TARGET_DIR"

download_file "onnx_inference.py"
download_file "tokenizer.json" "onnx_models/tokenizer.json"
download_file "onnx_models/encoder_conv.onnx"
download_file "onnx_models/encoder_conv.onnx.data"
download_file "onnx_models/encoder_transformer.onnx"
download_file "onnx_models/encoder_transformer.onnx.data"
download_file "onnx_models/decoder_init.int8.onnx"
download_file "onnx_models/decoder_step.int8.onnx"
download_file "onnx_models/embed_tokens.bin"

echo "Qwen ONNX artifact ready: $TARGET_DIR"
