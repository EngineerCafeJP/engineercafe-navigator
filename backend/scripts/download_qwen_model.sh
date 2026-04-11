#!/bin/bash
# Download Qwen3-ASR 0.6B model via qwen_asr library
# Caches model weights in HF_HOME for Docker build layer reuse.
#
# Usage:
#   bash scripts/download_qwen_model.sh
#   HF_HOME=/custom/cache bash scripts/download_qwen_model.sh

set -e

export QWEN_ASR_MODEL_ID="${QWEN_ASR_MODEL_ID:-Qwen/Qwen3-ASR-0.6B}"
export HF_HOME="${HF_HOME:-/app/.hf_cache}"

echo "[download] Qwen3-ASR model: $QWEN_ASR_MODEL_ID -> $HF_HOME ..."

python -c "
import os
from qwen_asr import Qwen3ASRModel
import torch

model_id = os.environ['QWEN_ASR_MODEL_ID']
hf_home = os.environ.get('HF_HOME', '/app/.hf_cache')

model = Qwen3ASRModel.from_pretrained(
    model_id,
    torch_dtype=torch.float32,
    device_map='cpu',
    low_cpu_mem_usage=True,
    max_new_tokens=256,
)
print(f'[done] Qwen model cached at {hf_home}')
"
