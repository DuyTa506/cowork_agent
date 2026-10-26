# OCR (Peppercorn v3): batch service

**Status: tested, works on stock vLLM 0.32.0** (the `vllm_student` plugin of v1/v2 is not needed).

- Checkpoint: `runs/v3-main/d48sh-muon` (step 126000, `Qwen3_5ForConditionalGeneration`, ~0.3B, `model.safetensors` 623 MB).
  It is not yet known whether the `ema/` copy or the base copy is the official final one: the base copy is used, as requested.
- `models/ocr-peppercorn-v3-d48sh-muon/` holds only the parts needed for serving (weights, config, tokenizer, processor, `vocab_map.json`),
  hard-linked to the original checkpoint, **without** `trainer_state.pt` (3 GB) or training logs. The `models/` folder is excluded by `.gitignore`.
- Flags follow `peppercorn-v3/bench/infer.py` (kind "qwen35"): one image per request, thinking off, `--no-enable-prefix-caching`,
  `--mm-processor-cache-gb 0`. OCR does not need prefix caching because every page is a different image; vLLM still allocates KV cache for
  decoding (about 2.6 GiB, 308k tokens).
- Tested on a public Vietnamese page (2048 px, 2894 input tokens, 850 output tokens): 2.7 s, Vietnamese output with correct diacritics,
  and a second call gave the same result (greedy). Quality and multi-page throughput have not been measured: that belongs to the Peppercorn side.

Usage: one page per request to `/v1/chat/completions` (only the page image, no text), `temperature 0`, with the image downscaled
client-side to a longest side of at most 2048 px. Batch operation: `scripts/up.sh ocr` when there are scans, `scripts/down.sh ocr` when done.

**Internal data:** the checkpoint was trained on internal documents. Keep it local; do not upload, commit or push it
(even once this repo has a remote). `.gitignore` blocks `*.safetensors`, `*.pt`, `*.bin` and `models/`.
