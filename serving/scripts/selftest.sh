#!/bin/bash
# Adapter contract test with fake backends: no GPU, no model, no Internet. Needs the vLLM image only.
. "$(dirname "$0")/lib.sh"
dk run --rm --entrypoint python3 -v "$D/adapter:/adapter:ro" "$IMAGE" /adapter/selftest.py
