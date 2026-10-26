#!/bin/bash
# Copy bge-reranker-v2-m3 from the local Hugging Face cache into /opt/intramind/models/rerank (real files, no symlinks).
set -e
SRC=$(ls -d "$HOME"/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/* | head -1)
DST=/opt/intramind/models/rerank/bge-reranker-v2-m3
[ -e "$DST" ] && { echo "$DST already exists"; exit 0; }
mkdir -p "$DST" && cp -rL "$SRC"/. "$DST"/ && echo "staged $DST" && du -sh "$DST"
