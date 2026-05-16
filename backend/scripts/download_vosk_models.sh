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
JA_MODEL_SHA256="efa092d280153a77615e9e0c7d7283e93e600de3d19d3bec686c57ef19d52eac"
EN_MODEL_SHA256="30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"

JA_TARGET="$MODEL_DIR/vosk-model-ja"
EN_TARGET="$MODEL_DIR/vosk-model-en-us"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

download_archive() {
    local url="$1"
    local tmpzip="$2"
    local name="$3"

    if curl -L --fail --retry 3 --retry-delay 2 -o "$tmpzip" "$url"; then
        return
    fi

    echo "[warn] TLS-verified download failed for $name; retrying with certificate checks disabled."
    echo "[warn] Archive integrity is still enforced by pinned SHA-256."
    curl -k -L --fail --retry 3 --retry-delay 2 -o "$tmpzip" "$url"
}

download_model() {
    local url="$1"
    local target="$2"
    local name="$3"
    local expected_sha256="$4"

    if [ -d "$target" ]; then
        echo "[skip] $name already exists at $target"
        return
    fi

    echo "[download] $name from $url ..."
    tmpzip=$(mktemp /tmp/vosk-XXXXXX.zip)
    download_archive "$url" "$tmpzip" "$name"

    actual_sha256=$(sha256_file "$tmpzip")
    if [ "$actual_sha256" != "$expected_sha256" ]; then
        echo "[error] SHA-256 mismatch for $name" >&2
        echo "[error] expected: $expected_sha256" >&2
        echo "[error] actual:   $actual_sha256" >&2
        rm -f "$tmpzip"
        exit 1
    fi

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

download_model "$JA_MODEL_URL" "$JA_TARGET" "Japanese (small)" "$JA_MODEL_SHA256"
download_model "$EN_MODEL_URL" "$EN_TARGET" "English (small)" "$EN_MODEL_SHA256"

echo ""
echo "Vosk models ready:"
ls -ld "$JA_TARGET" "$EN_TARGET"
