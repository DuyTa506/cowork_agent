#!/bin/bash
# usage: scripts/down.sh [llm|embed|rerank|adapter|ocr|all]   (all = everything of this repo; never touches other containers)
. "$(dirname "$0")/lib.sh"
what=${1:-all}
[ "$what" = all ] && set -- adapter rerank embed ocr llm || set -- "$what"
for n in "$@"; do dk rm -f "qk3-$n" 2>/dev/null && echo "stopped qk3-$n" || true; done
