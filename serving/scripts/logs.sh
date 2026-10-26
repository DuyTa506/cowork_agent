#!/bin/bash
. "$(dirname "$0")/lib.sh"; dk logs --tail "${2:-80}" "${1:?usage: logs.sh qk3-llm|qk3-embed|qk3-rerank|qk3-adapter|qk3-ocr [lines]}"
