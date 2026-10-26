#!/bin/bash
# Shared helpers. Source from the other scripts.
D=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# config: .env if present, else .env.example; variables already set in the environment win
envfile="$D/.env"; [ -f "$envfile" ] || { envfile="$D/.env.example"; echo "(no .env: using .env.example defaults)" >&2; }
declare -A _pre
for _k in $(grep -oE '^[A-Z_0-9]+=' "$D/.env.example" | tr -d =); do [ -n "${!_k+x}" ] && _pre[$_k]=${!_k}; done
set -a; . "$envfile"; set +a
for _k in "${!_pre[@]}"; do export "$_k=${_pre[$_k]}"; done
IMAGE=${IMAGE:-vllm/vllm-openai:v0.32.0}
GPU=${GPU:-0}
BIND_ADDR=${BIND_ADDR:-127.0.0.1}
PKG=/usr/local/lib/python3.12/dist-packages/vllm
mkdir -p "$D/.cache/vllm" "$D/.cache/flashinfer" "$D/logs"

# docker, or `sg docker -c docker ...` when the current shell is not in the docker group
dk() {
  if docker info >/dev/null 2>&1; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi
}
running() { [ -n "$(dk ps -q -f name=^/$1$)" ]; }
wait_health() { # name url timeout_s
  local i; for ((i = 0; i < $3 / 5; i++)); do
    curl -sf "$2" >/dev/null 2>&1 && { echo "$1 ready"; return 0; }
    running "$1" || { echo "$1 stopped, last log lines:" >&2; dk logs --tail 25 "$1" >&2; return 1; }
    sleep 5
  done; echo "$1 not ready after $3 s (see: scripts/logs.sh $1)" >&2; return 1
}
# Mount argument for a model dir; sets MOUNT_ARG and MODEL_PATH (path inside the container). Call it directly, not in $(...).
# A Hugging Face snapshot dir holds symlinks into ../../blobs, so the whole model dir is mounted in that case.
model_mount() { # dir target
  local dir=$1 target=$2
  if [[ $dir == */snapshots/* ]]; then MODEL_PATH=$target/snapshots/${dir##*/snapshots/}; MOUNT_ARG="${dir%%/snapshots/*}:$target:ro"
  else MODEL_PATH=$target; MOUNT_ARG="$dir:$target:ro"; fi
}
need_dir() { [ -n "$2" ] && [ -d "$2" ] || { echo "$1 is not set or not a directory ('$2'). Edit .env." >&2; return 2; }; }
