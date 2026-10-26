#!/bin/bash
# usage: scripts/up.sh [llm|embed|rerank|adapter|ocr|all]   (all = llm, embed, rerank, adapter; OCR is separate on purpose)
# Order matters: vLLM checks free GPU memory at start, so the biggest service goes first.
. "$(dirname "$0")/lib.sh"
what=${1:-all}

up_llm() {
  need_dir LLM_DIR "$LLM_DIR" || return 2
  [ -f "$D/vllm_patches/vllm/v1/attention/backends/sm120_fp8_fmha_glue.py" ] || { echo "vllm_patches missing" >&2; return 1; }
  local P=$D/vllm_patches/vllm
  dk rm -f qk3-llm >/dev/null 2>&1 || true
  # --- tuned scheduler + patches 01-05 of github.com/DuyTa506/sm120-vllm-kernels (CONFIG=next), vendored in vllm_patches/ ---
  dk run -d --name qk3-llm --restart "${RESTART_POLICY:-no}" --gpus device=$GPU --ipc=host --entrypoint vllm \
    -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -e VLLM_SM120_FP8_PREFILL=1 -e VLLM_SM120_FP8_PREFILL_NOGLUE=1 -e VLLM_FI_KERNEL_PAGES=16 \
    -e VLLM_GDN_INTERNAL_CKPT=1 -e VLLM_GDN_FUSED_CONV=1 \
    -v "$LLM_DIR:/models/llm:ro" -v "$D/.cache/vllm:/root/.cache/vllm" -v "$D/.cache/flashinfer:/root/.cache/flashinfer" \
    -v $P/v1/attention/backends/flashinfer.py:$PKG/v1/attention/backends/flashinfer.py:ro \
    -v $P/v1/attention/backends/sm120_fp8_fmha_glue.py:$PKG/v1/attention/backends/sm120_fp8_fmha_glue.py:ro \
    -v $P/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py:$PKG/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py:ro \
    -v $P/model_executor/layers/mamba/ops/fused_conv_post_conv.py:$PKG/model_executor/layers/mamba/ops/fused_conv_post_conv.py:ro \
    -p $BIND_ADDR:$LLM_PORT:8000 "$IMAGE" \
    serve /models/llm --served-model-name "$LLM_MODEL_NAME" --language-model-only \
    --max-model-len "$LLM_MAX_LEN" --max-num-seqs "$LLM_MAX_SEQS" --gpu-memory-utilization "$LLM_GPU_UTIL" \
    --enable-chunked-prefill --enable-prefix-caching --async-scheduling \
    --speculative-config '{"method":"mtp","num_speculative_tokens":2}' \
    --max-num-batched-tokens 16384 --cudagraph-capture-sizes $(cat "$D/vllm_patches/cudagraph_sizes.txt") --block-size 2176 \
    --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --enable-prompt-tokens-details \
    $LLM_EXTRA_ARGS >/dev/null
  wait_health qk3-llm "http://127.0.0.1:$LLM_PORT/health" 900
}

up_pool() { # name port dir target-model-name util max_len
  local name=$1 port=$2 dir=$3 served=$4 util=$5 maxlen=$6
  need_dir "$name dir" "$dir" || return 2
  model_mount "$dir" /models/m
  dk rm -f "$name" >/dev/null 2>&1 || true
  dk run -d --name "$name" --restart "${RESTART_POLICY:-no}" --gpus device=$GPU --ipc=host --entrypoint vllm \
    -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -v "$MOUNT_ARG" -v "$D/.cache/vllm:/root/.cache/vllm" \
    -p 127.0.0.1:$port:8000 "$IMAGE" \
    serve "$MODEL_PATH" --runner pooling --served-model-name "$served" --max-model-len "$maxlen" \
    --max-num-batched-tokens "$maxlen" --gpu-memory-utilization "$util" >/dev/null
  wait_health "$name" "http://127.0.0.1:$port/health" 600
}
up_embed() { up_pool qk3-embed "$EMBED_BACKEND_PORT" "$EMBED_DIR" "$EMBED_MODEL_NAME" "$EMBED_GPU_UTIL" "${EMBED_MAX_LEN:-32768}"; }
up_rerank() {
  local dir=$RERANK_DIR
  [ -n "$dir" ] || { dir=$(ls -d /opt/intramind/models/rerank/bge-reranker-v2-m3 2>/dev/null || ls -d "$HOME"/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/* 2>/dev/null | head -1); }
  up_pool qk3-rerank "$RERANK_BACKEND_PORT" "$dir" "$RERANK_MODEL_NAME" "$RERANK_GPU_UTIL" "${RERANK_MAX_LEN:-8192}"
}
up_adapter() {
  dk rm -f qk3-adapter >/dev/null 2>&1 || true
  dk run -d --name qk3-adapter --restart "${RESTART_POLICY:-no}" --network host --entrypoint python3 \
    -e EMBED_BACKEND_URL=http://127.0.0.1:$EMBED_BACKEND_PORT -e RERANK_BACKEND_URL=http://127.0.0.1:$RERANK_BACKEND_PORT \
    -e EMBED_MODEL_NAME="$EMBED_MODEL_NAME" -e RERANK_MODEL_NAME="$RERANK_MODEL_NAME" \
    -e EMBED_MAX_TOKENS="$EMBED_MAX_TOKENS" -e EMBED_MAX_BATCH="$EMBED_MAX_BATCH" \
    -e RERANK_MAX_TOKENS="$RERANK_MAX_TOKENS" -e RERANK_MAX_BATCH="$RERANK_MAX_BATCH" \
    -e EMBED_QUERY_PREFIX="$EMBED_QUERY_PREFIX" \
    -v "$D/adapter:/adapter:ro" "$IMAGE" -m uvicorn --app-dir /adapter app:app --host "$BIND_ADDR" --port "$ADAPTER_PORT" >/dev/null
  wait_health qk3-adapter "http://127.0.0.1:$ADAPTER_PORT/health" 120
}
up_ocr() {
  need_dir "OCR_DIR (Peppercorn checkpoint not chosen yet, see ocr/README.md)" "$OCR_DIR" || return 2
  dk rm -f qk3-ocr >/dev/null 2>&1 || true
  # flags follow peppercorn-v3 bench/infer.py (kind "qwen35"): one image per request, no prefix cache, thinking off
  dk run -d --name qk3-ocr --restart "${RESTART_POLICY:-no}" --gpus device=$GPU --ipc=host --entrypoint vllm \
    -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e OMP_NUM_THREADS=8 -v "$OCR_DIR:/models/ocr:ro" -v "$D/.cache/vllm:/root/.cache/vllm" \
    -p $BIND_ADDR:$OCR_PORT:8000 "$IMAGE" \
    serve /models/ocr --served-model-name "$OCR_MODEL_NAME" --max-model-len "${OCR_MAX_LEN:-16384}" \
    --limit-mm-per-prompt '{"image":1}' --gpu-memory-utilization "$OCR_GPU_UTIL" --max-num-seqs "${OCR_MAX_SEQS:-16}" \
    --no-enable-prefix-caching --mm-processor-cache-gb 0 --api-server-count 2 --disable-uvicorn-access-log \
    --default-chat-template-kwargs '{"enable_thinking": false}' >/dev/null
  wait_health qk3-ocr "http://127.0.0.1:$OCR_PORT/health" 600
}

case $what in
  llm) up_llm ;; embed) up_embed ;; rerank) up_rerank ;; adapter) up_adapter ;; ocr) up_ocr ;;
  all) up_llm && up_embed && up_rerank && up_adapter ;;
  *) echo "usage: $0 [llm|embed|rerank|adapter|ocr|all]" >&2; exit 1 ;;
esac
