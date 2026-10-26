#!/bin/bash
# Health of every service of this repo; exit code 1 if a running one is unhealthy. OCR is optional (batch).
. "$(dirname "$0")/lib.sh"
rc=0
chk() { # label url required
  if curl -sf -m 5 "$2" >/dev/null 2>&1; then printf '%-10s ok   %s\n' "$1" "$2"
  else printf '%-10s %-4s %s\n' "$1" "$([ "$3" = 1 ] && echo DOWN || echo off)" "$2"; [ "$3" = 1 ] && rc=1; fi
}
chk llm     "http://127.0.0.1:$LLM_PORT/health" 1
chk embed   "http://127.0.0.1:$EMBED_BACKEND_PORT/health" 1
chk rerank  "http://127.0.0.1:$RERANK_BACKEND_PORT/health" 1
chk adapter "http://127.0.0.1:$ADAPTER_PORT/health" 1
chk ocr     "http://127.0.0.1:$OCR_PORT/health" 0
echo "GPU memory used: $(nvidia-smi --id=$GPU --query-gpu=memory.used,memory.total --format=csv,noheader)"
exit $rc
