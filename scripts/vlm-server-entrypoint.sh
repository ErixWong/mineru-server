#!/bin/sh
# vlm-server entrypoint
#
# Fixes for local GPU deployment of MinerU2.5 VLM models via vLLM.
#
# Why this script exists (two known pitfalls):
#
# 1. transformers version incompatibility
#    The official `vllm/vllm-openai:v0.21.0` image ships transformers 5.8.1.
#    MinerU2.5 models (e.g. MinerU2.5-Pro-2605-1.2B) are trained with
#    transformers 4.57.x; loading them with 5.8.1 silently breaks
#    `tie_word_embeddings` (lm_head is randomly initialized), which makes the
#    model output garbage. We pin transformers==4.57.6 (vLLM requires
#    transformers>=4.56.0 and !=5.0-5.5.0, so 4.57.6 satisfies the constraint).
#
# 2. mineru-vl-utils + MinerULogitsProcessor
#    MinerU's own vllm server wrapper (mineru/model/vlm/vllm_server.py) appends
#    `--logits-processors mineru_vl_utils:MinerULogitsProcessor` to the vLLM
#    command. That processor enforces no-repeat-n-gram while generating layout
#    JSON. Without it the VLM output repeats n-grams and the layout cannot be
#    parsed (tasks finish with empty block lists). The package is not part of
#    the plain vllm image, so we install it here.

set -e

# --- Fix 1: pin transformers to a MinerU-compatible version ---
if ! python3 -c "import transformers; assert transformers.__version__.startswith('4.57')" 2>/dev/null; then
  echo "[entrypoint] Pinning transformers==4.57.6 (MinerU model compatibility)..."
  pip install -q --no-cache-dir "transformers==4.57.6"
fi

# --- Fix 2: ensure mineru-vl-utils provides MinerULogitsProcessor ---
if ! python3 -c "import mineru_vl_utils" 2>/dev/null; then
  echo "[entrypoint] Installing mineru-vl-utils..."
  pip install -q --no-cache-dir "mineru-vl-utils>=1.0.5,<2"
fi

echo "[entrypoint] Starting vllm serve: $*"
exec vllm serve "$@"
