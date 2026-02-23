#!/bin/bash
# Download and convert Helsinki-NLP/opus-mt translation models for CTranslate2.
#
# Creates int8-quantized CTranslate2 models + SentencePiece tokenizer files.
#
# Models:
#   opus-mt-en-jap  (EN -> JA)  ~150 MB int8
#   opus-mt-ja-en   (JA -> EN)  ~150 MB int8
#
# Requirements (build-time only):
#   pip install ctranslate2 transformers torch sentencepiece
#
# Usage:
#   bash scripts/download_translation_models.sh              # default: models/translation
#   bash scripts/download_translation_models.sh /custom/dir  # custom directory

set -e

MODEL_DIR="${1:-models/translation}"
mkdir -p "$MODEL_DIR"

HF_BASE="https://huggingface.co/Helsinki-NLP"

# ──────────────────────────────────────────────────────────
# Helper: convert one model
# ──────────────────────────────────────────────────────────
convert_model() {
    local hf_name="$1"   # e.g. opus-mt-en-jap
    local label="$2"     # e.g. "EN -> JA"
    local target="$MODEL_DIR/$hf_name"

    if [ -f "$target/model.bin" ] && [ -f "$target/source.spm" ] && [ -f "$target/target.spm" ]; then
        echo "[skip] $label model already exists at $target"
        return
    fi

    echo ""
    echo "============================================"
    echo " Converting $label ($hf_name)"
    echo "============================================"

    # Step 1: CTranslate2 conversion (needs torch + transformers)
    echo "[1/2] Converting Helsinki-NLP/$hf_name to CTranslate2 int8 ..."
    ct2-transformers-converter \
        --model "Helsinki-NLP/$hf_name" \
        --quantization int8 \
        --output_dir "$target" \
        --force

    # Step 2: Download SentencePiece tokenizer files from HuggingFace
    echo "[2/2] Downloading SentencePiece tokenizer files ..."
    for spm_file in source.spm target.spm; do
        if [ ! -f "$target/$spm_file" ]; then
            curl -sL -o "$target/$spm_file" \
                "$HF_BASE/$hf_name/resolve/main/$spm_file"
            echo "  -> $spm_file downloaded"
        else
            echo "  -> $spm_file already present"
        fi
    done

    echo "[done] $label model ready at $target"
}

# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

# Check for required tools
if ! command -v ct2-transformers-converter &> /dev/null; then
    echo "ERROR: ct2-transformers-converter not found."
    echo "Install with: pip install ctranslate2 transformers torch sentencepiece"
    exit 1
fi

convert_model "opus-mt-en-jap" "EN -> JA"
convert_model "opus-mt-ja-en"  "JA -> EN"

echo ""
echo "Translation models ready:"
ls -ld "$MODEL_DIR"/opus-mt-*/
