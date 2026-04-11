#!/bin/bash
# Download Qwen3-ASR 0.6B model via qwen_asr library
# Caches model weights in HF_HOME for Docker build layer reuse.
#
# Usage:
#   bash scripts/download_qwen_model.sh
#   HF_HOME=/custom/cache bash scripts/download_qwen_model.sh

set -e

MODEL_ID="${QWEN_ASR_MODEL_ID:-Qwen/Qwen3-ASR-0.6B}"
HF_HOME="${HF_HOME:-/app/.hf_cache}"
export HF_HOME

echo "[download] Qwen3-ASR model: $MODEL_ID -> $HF_HOME ..."

python -c "
from qwen_asr import Qwen3ASRModel
import torch

model = Qwen3ASRModel.from_pretrained(
    '${MODEL_ID}',
    torch_dtype=torch.float32,
    device_map='cpu',
    low_cpu_mem_usage=True,
    max_new_tokens=256,
)
print('[done] Qwen model cached at ${HF_HOME}')
"
