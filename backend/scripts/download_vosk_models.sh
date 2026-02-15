#!/bin/bash
# Download Vosk speech recognition models (small versions for dev/test)
# Japanese: 48MB, English: 40MB
#
# Usage:
#   bash scripts/download_vosk_models.sh
#   bash scripts/download_vosk_models.sh /custom/model/dir

set -e

MODEL_DIR="${1:-models}"
mkdir -p "$MODEL_DIR"

JA_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip"
EN_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

JA_TARGET="$MODEL_DIR/vosk-model-ja"
EN_TARGET="$MODEL_DIR/vosk-model-en-us"

download_model() {
    local url="$1"
    local target="$2"
    local name="$3"

    if [ -d "$target" ]; then
        echo "[skip] $name already exists at $target"
        return
    fi

    echo "[download] $name from $url ..."
    tmpzip=$(mktemp /tmp/vosk-XXXXXX.zip)
    curl -L -o "$tmpzip" "$url"

    echo "[extract] $name ..."
    tmpdir=$(mktemp -d /tmp/vosk-extract-XXXXXX)
    unzip -q "$tmpzip" -d "$tmpdir"

    # The zip extracts to a versioned directory name; rename to expected path
    extracted_dir=$(ls -d "$tmpdir"/vosk-model-* | head -1)
    mv "$extracted_dir" "$target"

    rm -f "$tmpzip"
    rm -rf "$tmpdir"
    echo "[done] $name -> $target"
}

download_model "$JA_MODEL_URL" "$JA_TARGET" "Japanese (small)"
download_model "$EN_MODEL_URL" "$EN_TARGET" "English (small)"

echo ""
echo "Vosk models ready:"
ls -ld "$JA_TARGET" "$EN_TARGET"
